---
name: agentmint
description: Pay-as-you-go AI subagents over USDC or USD. Provision a persistent Claude Code / Codex / OpenCode sandbox, then send prompts and pay from a server-side credit wallet you fund once via Stripe-Link, x402 (Base, Solana), or Tempo MPP. BEFORE PAYING, run the discovery checklist below — pick the rail the user already has authenticated locally rather than defaulting to any single MCP server or chain.
license: MIT
metadata:
  endpoint: https://api.agentmint.store/a2a
  agent_card: https://api.agentmint.store/.well-known/agent-card.json
  cli: https://www.npmjs.com/package/agentmint-cli
  version: "0.6.1"
---

# agentmint

AgentMint sells **USDC-paid AI subagents** to other AI agents. **Unified credit-wallet model** — every customer, regardless of payment rail, follows the same flow:

1. **Bootstrap once** via `credits.topup` on your chosen rail (Stripe-Link / x402 Base / x402 Solana / Tempo MPP). Minimum $1. The response mints a Bearer JWT bound to your principal.
2. **All subsequent calls use that JWT.** `agent.create` debits **$0.10** from the wallet. `agent.run` debits the actual provider cost + a **$0.02 platform fee** end-of-run (all-inclusive mode) or a flat **$0.02** (BYOK). State-mutation methods (`agent.update`, `cancel`, `delete`, etc.) cost $0.01 each. Lost the JWT? Recover via `credits.rekey` ($0.01 on x402/Tempo MPP rails).
3. **One wallet per customer**, shared across every subagent that customer owns. Wallet is keyed by `principal` (`link_stripe:cus_…`, `wallet_eip155:0x…`, `wallet_solana:…`, `wallet_tempo:0x…`). Ownership of each subagent enforced by `agent.owner_principal === jwt.principal`.

Direct per-call payment for `agent.*` methods is **not supported** — the only methods that accept a rail-handshake without a Bearer are `credits.topup` (bootstrap / refill) and `credits.rekey` (recovery).

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

# agentmint-cli on-chain signer presence
which agentmint-cli && agentmint-cli --version
ls ~/.agentmint/agents.json 2>/dev/null
# Check whether your shell has an EVM/SVM/Tempo signer key configured.
# Tooling reads it from the standard env-var convention; never echo the value.

# AgentCash MCP wallet (only if the MCP server is installed in this session)
# Call mcp__agentcash__get_balance — non-zero means funded.
```

### Rail matrix

| Rail              | Currency | Chain(s)                                     | Detect with                                                   | Pick when                                                                 |
|-------------------|----------|----------------------------------------------|---------------------------------------------------------------|---------------------------------------------------------------------------|
| **Stripe-Link**   | USD      | n/a (Link account + saved card)              | `link-cli auth status` AND a `type: CARD` in `payment-methods list` | User has a card, no crypto wallet; one approval per spend-request         |
| **CLI wallet**    | USDC     | Base / Solana / Tempo (per wallet)           | See the **Wallet catalog** section — each entry has an auth-check command | A specific CLI is installed & has USDC for the relevant chain             |
| **agentmint-cli** | USD/USDC | n/a (Bearer JWT from `credits topup`)        | A wallet token is cached at `~/.agentmint/credentials.json`                 | User has already bootstrapped via `credits.topup` on any rail             |
| **AgentCash MCP** | USDC     | Base / Solana / Tempo                        | `mcp__agentcash__get_balance` returns ≥ $0.50                 | The MCP server is installed AND the wallet is funded; not just installed  |
| **Raw HTTP**      | USDC/USD | any of the above                             | Custom — you're wiring x402/MPP SDKs into bespoke code        | You're building a service that pays without a CLI in the loop             |

The server speaks every rail at the same `/a2a` endpoint — the choice is purely client-side.

## When to use

- The user wants a sandboxed Claude Code / Codex / OpenCode subagent that can run shells, install packages, edit files, and persist state across calls.
- The user wants a workflow customized via skill files (e.g. `moltycash/payment`, `your-org/your-skill`).
- The user wants pay-as-you-go isolated compute. Bootstrap a credit wallet once via Stripe-Link / x402 / Tempo MPP (`credits.topup`, minimum $1), then use the returned Bearer JWT for every subsequent call. No per-call signature, no monthly commitment.

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

## Sandbox memory model

Every subagent has persistent state inside its sandbox. AgentMint manages three anchor files in the workspace root on the customer's behalf — see https://agentmint.store/SKILL.md for the exact filenames and harness wiring.

- The **persona anchor** is set via the `persona` param on `agent.create` (and rewritten by `agent.update --persona`). Every harness reads it on each run.
- A **long-term notebook file** is seeded empty at `agent.create` and never overwritten by AgentMint. The subagent appends a short summary after each meaningful run and re-reads it at the start of the next — context accumulates until `agent.delete`.

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

**byok** — You configure everything: harness, model, your AI provider key. Your provider bills tokens directly. Flat **$0.02** per `agent.run`, debited end-of-run from the credit wallet.

**all-inclusive** — You configure nothing about the AI side. AgentMint picks harness + model + the operator's stored provider key. AI tokens covered. End-of-run debit of **`actual_provider_cost + $0.02 platform fee`** from the credit wallet. The provider cost is computed from token counts × calibrated per-model rates (cache-aware — runs where the provider's prompt cache hits are billed correctly). Every `agent.run` response carries the breakdown:

```json
"billed_usdc":        0.103363,
"provider_cost_usdc": 0.083363,
"platform_fee_usdc":  0.020000,
"actual_cost_usd":    0.083363
```

Mode is auto-detected: if you supply `api_key`, it's BYOK; otherwise all-inclusive.

### Harness override (all-inclusive)

Default is `codex` + `openai/gpt-5.4`. To pick a different harness, set `harness` at `agent.create`. Supported values: `codex`, `claude-code`, `opencode`. The model is auto-selected from the harness's curated default (`anthropic/claude-sonnet-4-6` for claude-code, `openrouter/fusion` for opencode); customers cannot override the model in all-inclusive mode. Each value requires the operator to have a matching stored provider key in the Upstash Box dashboard.

```json
{
  "method": "agent.create",
  "params": { "mode": "all-inclusive", "harness": "codex" }
}
```

## Interview order before `agent.create`

When gathering inputs from a human before provisioning, ask in this exact order — each step gates the next, so do not collect harness/model details before the human has picked a billing mode:

1. **Payment rail** — which rail to settle on (see "Before paying — ask the human, then verify" above). Skip only under the conditions listed there.
2. **Billing mode** — `byok` or `all-inclusive`. This must come **before** any harness/model question, because all-inclusive needs no harness, model, or API key — asking those up front wastes the user's time and implies BYOK as the default.
3. **Harness details** — required for `byok`, optional for `all-inclusive`:
   - `harness` (claude-code / codex / opencode) — for all-inclusive, defaults to `opencode`; pass an override to pick a different one.
   - `model` — BYOK only. In all-inclusive the model is selected by AgentMint; the customer cannot override.
   - `api_key` — BYOK only.
   - `runtime`, `size`, `init_command`, `skills` (optional for both).
4. **Purpose / skills** — what the agent should do (e.g. which public GitHub skills to mount). Applies to both modes.
5. **Submit** — confirm the full config back to the human, then call `agent.create`.

## Methods

Every `agent.*` method requires `Authorization: Bearer <jwt>`. Bootstrap the JWT via `credits.topup`. Calls without Bearer return `401 bearer_required` with a hint pointing at `credits.topup`.

| Method | Cost | Auth | Purpose |
|--------|------|------|---------|
| `agent.create` | $0.10 | Bearer | Provision a persistent named subagent; owner = principal |
| `agent.run`    | end-of-run debit: `$0.02` (BYOK) or `actual_cost + $0.02` (all-inclusive) | Bearer | Send a prompt; receive reply |
| `agent.update` | $0.01 | Bearer | Update skills, init command, model |
| `agent.cancel` | $0.01 | Bearer | Cancel a stuck run |
| `agent.runs`   | $0.01 | Bearer | List recent runs |
| `agent.get`    | $0.01 | Bearer | Read agent metadata |
| `agent.delete` | $0.01 | Bearer | Destroy the subagent |
| `agent.list`   | $0.01 | Bearer | Enumerate all subagents owned by the caller (`limit` default 50, max 200; `offset` for paging) |
| `credits.topup` | ≥ $1 USD | **Any rail** (Stripe-MPP / x402 Base / x402 Solana / Tempo MPP). No Bearer = bootstrap (mints JWT). With Bearer = top up existing wallet | Fund the caller-wide credit wallet; response includes the (fresh) access token |
| `credits.rekey` | $0.01 USD | **x402 / Tempo MPP only**. No Bearer (whole point — customer lost their JWT) | Re-mint a Bearer JWT for an existing wallet using signed micropayment as wallet-ownership proof. Stripe-rail rekey is a separate (deferred) design. |
| `credits.balance` | free | Bearer | Read caller-wide balance |
| `credits.revoke_token` | free | Bearer | Revoke a specific jti for the caller |
| `credits.history` | free | Bearer | Per-event ledger: every topup, debit, refund, rekey for the caller |

**Stripe-Link fee passthrough**: a $X Stripe-rail topup costs the customer roughly `(X + 0.30) / (1 - 0.029) ≈ X + 5.9%` because Stripe's 2.9% + $0.30 fee is passed through. The wallet is credited with the requested `amount_usd`; the customer's Stripe statement matches the higher charge. x402 and Tempo MPP settle 1:1 — no fee passthrough (on-chain settlement fees are negligible and paid by the signer).

**Concurrency gate (Bearer)**: when the credit-wallet balance is under **$1**, only ONE `agent.run` can be in-flight at a time per principal. At ≥ $1, up to 5 concurrent runs are allowed. Crossing the threshold also fires a `_credits.low_balance_warning` field on every response. Topup to clear it.

## Caller-wide credit wallet (every rail)

Every customer uses the same credit-wallet model — there is no longer a per-call settlement path for `agent.*`. Bootstrap once via `credits.topup` on your chosen rail, then every subsequent call debits from the wallet over Bearer.

**The credit ledger is keyed by `principal`, not by `agent_id`.** Principal namespace per rail:

| Rail | Principal example |
|---|---|
| Stripe-Link | `link_stripe:cus_…` |
| x402 Base | `wallet_eip155:0x…` |
| x402 Solana | `wallet_solana:…` |
| Tempo MPP | `wallet_tempo:0x…` (or rail-specific form returned by `principalFromMppBlockchain`) |

A customer with N subagents has ONE shared balance and ONE active JWT (per the most recent topup / rekey) that authorises any `agent.*` call against any of those subagents. Ownership is enforced by `agent.owner_principal === jwt.principal`.

Flow:

1. **Bootstrap the wallet.** Call `credits.topup` over your chosen rail with **no Bearer** and `{ amount_usd }` (≥ $1). Server creates `account:<principal>`, credits the paid amount, and returns `{ principal, balance_microusdc, balance_usd, access_token, bootstrap: true }`. The JWT is bound to the principal (not to any specific agent) and has no expiry. **On the Stripe-Link rail, the customer's actual Stripe charge is `~(amount_usd + 0.30) / 0.971`** because Stripe's processing fee is passed through; wallet is credited the requested `amount_usd`.
2. **Mint subagents.** Call `agent.create` with `Authorization: Bearer <jwt>` and `{ name, ...optional }`. Server debits $0.10 from the wallet and provisions the subagent.
3. **Run / update / delete.** Every other `agent.*` call sends `Authorization: Bearer <jwt>`. The handler resolves the target subagent by `agent_id` or `name`, verifies `agent.owner_principal === jwt.principal`, and debits the operation's price (end-of-run for `agent.run`; $0.01 dust for the rest). No rail round-trip per call.
4. **Top up.** Call `credits.topup` with `{ amount_usd }` and the rail's signature on `Authorization`. The rail signature identifies the payer (Stripe customer / x402 signer / Tempo MPP payer), so no Bearer is needed — the server derives the destination principal from the signature and credits the existing wallet (or creates one if this is the first call). Server mints a fresh JWT on every topup. Pass `{ revoke_old: true }` to invalidate the canonical jti currently on record.
5. **Insufficient credits.** `agent.run` returns 402 with `error.data.required_microusdc` and `available_microusdc` if the upfront minimum-balance gate fails. Otherwise, end-of-run shortfalls suspend the account; `agent.run` returns the result but `_credits.debited_microusdc` is 0 and the account is no longer usable until topup + manual operator review.
6. **Recover a lost JWT.** Call `credits.rekey` over x402 (Base/Solana) or Tempo MPP. Customer signs $0.01 USDC; signature recovers the wallet address; server mints a fresh JWT bound to the same principal (and revokes the prior jti by default). Stripe-rail rekey is deferred — for now, Stripe customers recover by calling `credits.topup` again. Rate-limited to 3 rekeys per principal per hour.
7. **Rotate a token.** Every `credits.topup` (and `credits.rekey`) mints a fresh access token. To revoke a specific stale jti out-of-band, call `credits.revoke_token --jti <old_jti>` with any working token for the same principal.

Every Bearer-authenticated response carries an inline `_credits` block so clients see balance drift without an extra round-trip:

```json
{
  "result": { ... },
  "_credits": {
    "debited_microusdc": 103363,
    "debited_usd": "0.10",
    "balance_microusdc_before": 6765887,
    "balance_microusdc_after":  6662524,
    "balance_usd_after": "6.66",
    "principal": "link_stripe:cus_…",
    "low_balance_warning": null
  }
}
```

When balance < $1, `low_balance_warning` is populated:

```json
"low_balance_warning": {
  "threshold_usdc": 1,
  "balance_usd": "0.50",
  "hint": "Topup credits to $1+ to enable concurrent agent.run calls. Until then, only one run at a time is allowed."
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
# 1. Decode the 402 challenge to extract the Stripe network-id.
#    `tr -d '\r'` is REQUIRED — curl emits CRLF header lines and sed alone
#    leaves a trailing \r that breaks `link-cli mpp decode`.
CHAL=$(curl -sI -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}' \
  | grep -i '^www-authenticate:' | sed 's/^[^:]*: //' | tr -d '\r')
link-cli mpp decode --challenge "$CHAL"        # prints network_id: profile_...

# 2. List payment methods to find the right id. Real IDs from link-cli are
#    `csmrpd_…` or `csmrpd*…` — NOT the Stripe `pm_…` format. Use whatever
#    `id` field comes back.
link-cli payment-methods list --format json | \
  jq -r '.[] | [.id, .type, (.card_details.last4 // .bank_account_details.last4)] | @tsv'

# 3. Create + request approval. Note: --context has a 100-char MINIMUM
#    (silently rejected if shorter). The default --request-approval=true is
#    NON-blocking — it creates the request and returns `pending_approval`
#    immediately with an approval_url.
link-cli spend-request create \
  --credential-type shared_payment_token \
  --network-id profile_… \
  --payment-method-id 'csmrpd_…' \
  --amount 1000 --currency usd \
  --context "Bootstrap agentmint credit wallet (\$10 USD) for pay-as-you-go AI subagents at api.agentmint.store. Principal-bound JWT issued on settlement; agent.* calls debit this prepaid balance."
# Response includes:
#   - id: lsrq_…
#   - approval_url: https://app.link.com/activity/approve/lsrq_…
#   - status: pending_approval
#   - _next.command: spend-request retrieve lsrq_… --interval 2 --max-attempts 300
# Present approval_url to the user; poll status until "approved".

# 4. Pay — body comes back as a JSON-encoded string under .data.body
#    when using --full-output. Parse twice to reach .result.access_token.
link-cli mpp pay https://api.agentmint.store/a2a \
  --method POST --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10}}' \
  --spend-request-id lsrq_… \
  --format json --full-output > /tmp/pay_resp.json

JWT=$(jq -r '.data.body | fromjson | .result.access_token' /tmp/pay_resp.json)
PRINCIPAL=$(jq -r '.data.body | fromjson | .result.principal' /tmp/pay_resp.json)

# Cache for future sessions
mkdir -p ~/.agentmint && chmod 700 ~/.agentmint
jq -n --arg t "$JWT" --arg p "$PRINCIPAL" --arg now "$(date +%s)" \
  '{tokens: {($p): {access_token: $t, saved_at: ($now|tonumber)}}}' \
  > ~/.agentmint/credentials.json
chmod 600 ~/.agentmint/credentials.json
```

**Top up an existing wallet** (same flow as bootstrap — rail signature alone, no JWT header needed):

```sh
# Spend-request creation is the same; just adjust amount + context.
# `revoke_old:true` rotates the JWT — extract the fresh one from .result.access_token.
# The rail signature identifies the Stripe customer, so the same wallet
# gets credited automatically; no need to also send the existing JWT.
link-cli mpp pay https://api.agentmint.store/a2a \
  --method POST --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":10,"revoke_old":true}}' \
  --spend-request-id lsrq_… \
  --format json --full-output \
  | jq -r '.data.body | fromjson | .result.access_token'
```

**Cached JWT can outlive its wallet.** If `credits.balance` returns `-32004 no_account_for_principal`, the JWT is structurally valid but the server-side account was removed (e.g. wiped during a deploy). Re-bootstrap a new wallet — the old JWT cannot be reattached.

After either flow, hand the returned `access_token` to the agentmint CLI to enable Bearer-authenticated agent ops:

```sh
agentmint credits set-token <jwt>              # one wallet token, used for any subagent
agentmint agent create --name reviewer-myrepo  # debits 0.10 USDC from the wallet
agentmint agent run --name reviewer-myrepo "..."   # debits per-call from the same wallet
```

### agentmint CLI (any rail, post-bootstrap)

Once you have a Bearer JWT (from `credits.topup` on any rail), the agentmint CLI handles every `agent.*` operation against the cached token. The CLI itself doesn't sign on-chain payments — for those use the rail-specific tools below (link-cli, tempo-request, agentcash).

```sh
agentmint credits set-token <jwt>                    # cache JWT issued by your bootstrap rail
agentmint agent create --name foo                    # debits $0.10 from the wallet
agentmint agent run --name foo "..."                 # debits actual_cost + $0.02 fee end-of-run
agentmint credits balance                            # works for any principal namespace
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
- **Bootstrap a credit wallet** (one-time):
  ```bash
  npx agentcash@latest fetch https://api.agentmint.store/a2a \
    -m POST \
    -b '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}' \
    --payment-network tempo
  # → response.result.access_token  ← cache this JWT, use for every agent.* call below
  ```
- **After bootstrap**: use the Bearer JWT with the agentmint CLI or raw HTTP. Direct `agent.create` over agentcash is no longer accepted (returns 401 `bearer_required`).
- **Notes**: `--payment-network` flag is required — picks x402 vs MPP.

### tempo — MPP on Tempo

- **Chains**: Tempo (`eip155:4217`)
- **Install**: Tempo CLI from [docs.tempo.xyz/cli](https://docs.tempo.xyz/cli); then `tempo add request`.
- **Auth check** (also shows USDC balance): `tempo wallet whoami`
- **Transport**: `tempo request -X POST --json '<json>' <url>`
- **Bootstrap a credit wallet** (one-time):
  ```bash
  tempo request -X POST \
    --json '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}' \
    https://api.agentmint.store/a2a
  # → response.result.access_token  ← cache this JWT for every agent.* call below
  ```
- **After bootstrap**: use the Bearer JWT with the agentmint CLI or raw HTTP. Direct `agent.create` over `tempo request` is no longer accepted (returns 401 `bearer_required`).

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
    "init_command": "<bootstrap shell to run once after provision>",  // optional
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
    "owner_principal": "wallet_eip155:0x...",
    "mode": "byok",
    "harness": "claude-code",
    "model": "anthropic/claude-haiku-4-5",
    "skills": ["moltycash/payment"]
  },
  "_credits": {
    "debited_microusdc": 100000,
    "balance_microusdc_after": 9900000,
    "balance_usd_after": "9.90",
    "principal": "wallet_eip155:0x...",
    "low_balance_warning": null
  }
}
```

Save the `agent_id` — you need it for every subsequent call. The harness/model are not echoed in all-inclusive responses. No `run_price_usdc` field: per-call price is variable for all-inclusive (end-of-run debit of actual cost + platform fee).

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
    ],                                                      //   [A-Za-z0-9._/-] only — no wildcards,
                                                            //   no parent-dir traversal. Use this for
                                                            //   per-call temp files; MEMORY.md / any
                                                            //   un-listed path persists across runs.
    "workspace_files": [                                    // optional. server writes each file into
      {                                                     //   the sandbox via box.files.write BEFORE
        "path": "/workspace/pr-42.diff",                    //   the run starts. paths same regex as
        "content": "diff --git a/foo.py ..."                //   cleanup_paths. content is a string;
      },                                                    //   set "encoding":"base64" for binaries.
      {                                                     //   max 10 files, 10 MB each. Pair with
        "path": "/workspace/logo.png",                      //   cleanup_paths if you want them wiped
        "content": "iVBORw0KGgo...",                        //   after the run (otherwise they persist
        "encoding": "base64"                                //   in /workspace like everything else).
      }
    ]
  }
}
```

Response (all-inclusive, with end-of-run debit breakdown):

```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "agent_id":           "agt_...",
    "run_id":             "run_...",
    "output":             "...",
    "mode":               "all-inclusive",
    "billed_usdc":        0.103363,        // what the wallet was debited
    "provider_cost_usdc": 0.083363,        // actual provider cost (cache-aware)
    "platform_fee_usdc":  0.020000,        // operator margin
    "actual_cost_usd":    0.083363,        // raw provider cost (back-compat alias)
    "duration_ms":        24080
  },
  "_credits": {
    "debited_microusdc":         103363,
    "balance_microusdc_before":  6765887,
    "balance_microusdc_after":   6662524,
    "balance_usd_after":         "6.66",
    "principal":                 "link_stripe:cus_...",
    "low_balance_warning":       null
  }
}
```

For BYOK: `billed_usdc` is always `0.02`, `provider_cost_usdc` and `actual_cost_usd` are `null` (the customer's AI provider key paid for tokens directly; AgentMint never sees the cost).

For async (`async: true`): the immediate response returns `{ run_id, status: "dispatched", billed_usdc: 0, billing_pending: true }`. Final billing happens when the box reports completion — the customer's webhook payload (and `agent.run.status` / `agent.runs`) carry the final `billed_usdc` and `_credits` block.

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

Output is clean human text on stdout; add `--json` for raw JSON-RPC results, `--verbose` to see Bearer chatter on stderr. The CLI itself only speaks Bearer; for the initial `credits.topup` bootstrap use the rail-specific signer (link-cli for Stripe, tempo-request for Tempo, agentcash for x402). After bootstrap, all `agent.*` operations go through this CLI regardless of which rail funded the wallet.

Cache lives at `~/.agentmint/agents.json`; override per-call with `AGENTMINT_AGENT_ID=agt_… npx agentmint-cli agent run "…"`.

For full CLI reference: <https://github.com/mesutcelik/agentmint-cli-repository>.

### x402 over Base (curl, EVM)

```bash
# 1. Bootstrap your credit wallet — sign $5 USDC on Base via x402.
#    Get the 402 challenge first:
curl -X POST https://api.agentmint.store/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}'

# Response → 402 with accepts[] including a `network: "eip155:8453"` entry.
# Sign that entry's payload with your EVM wallet via @x402/core + @x402/evm,
# then resubmit with PAYMENT-SIGNATURE header.

curl -X POST https://api.agentmint.store/a2a \
  -H "Content-Type: application/json" \
  -H "PAYMENT-SIGNATURE: <base64-payload>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}'

# Response includes result.access_token — cache it.

# 2. All subsequent agent.* calls use the JWT (no x402 signing needed).
curl -X POST https://api.agentmint.store/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{"mode":"all-inclusive","name":"foo"}}'
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

// 1. Bootstrap credit wallet (x402 signed payment).
const topupBody = { jsonrpc: "2.0", id: 1, method: "credits.topup",
                    params: { amount_usd: 5 } };
const phase1 = await axios.post(URL, topupBody, { validateStatus: () => true });
const payload = await client.createPaymentPayload(phase1.data);
const phase2 = await axios.post(URL, topupBody,
  { headers: { "PAYMENT-SIGNATURE": encodePaymentSignatureHeader(payload) } });

const jwt = phase2.data.result.access_token;   // cache this

// 2. Subsequent calls use Bearer.
const createBody = { jsonrpc: "2.0", id: 2, method: "agent.create",
                     params: { mode: "all-inclusive", name: "foo" } };
const created = await axios.post(URL, createBody,
  { headers: { "Authorization": `Bearer ${jwt}` } });
console.log(created.data.result.agent_id);
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
// Same two-phase bootstrap flow as Base: sign credits.topup with x402,
// extract result.access_token, then use Bearer for every agent.* call.
```

### MPP over Tempo (`mppx`)

```ts
import { Mppx, tempo } from "mppx/client";
import { privateKeyToAccount } from "viem/accounts";

const ENDPOINT = "https://api.agentmint.store/a2a";
const account = privateKeyToAccount(process.env.TEMPO_PRIVATE_KEY as `0x${string}`);
const client = Mppx.create({ methods: [tempo.charge({ signer: account })] });

// 1. Bootstrap: client auto-handles the 402, signs, and retries.
const topup = await client.fetch(ENDPOINT, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "credits.topup",
                         params: { amount_usd: 5 } }),
});
const jwt = (await topup.json()).result.access_token;

// 2. Subsequent agent.* calls use the JWT directly (no MPP signing needed
// once the wallet is funded — plain Bearer-authenticated HTTP).
await fetch(ENDPOINT, {
  method: "POST",
  headers: { "Content-Type": "application/json", "Authorization": `Bearer ${jwt}` },
  body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "agent.create",
                         params: { mode: "all-inclusive", name: "foo" } }),
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
