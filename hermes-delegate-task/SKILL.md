---
name: hermes-delegate-task
description: Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents — specialists that accumulate `/workspace/MEMORY.md` across calls. Catch-all default via `default_agent_name="general-worker"`; per-call specialist routing via an `agentmint-<name>` entry in `toolsets`. Polling delivery (no public HTTPS endpoint required); pay via any rail (Stripe-Link / x402 / Tempo MPP).
version: 0.9.1
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

- Hermes' session needs a **specialist** (PR reviewer, compliance checker, customer-support agent, codebase oracle, ...) that accumulates domain knowledge across days/weeks → pre-mint a named specialist and route per-call.
- A task fans out into N independent slices and each should land in its own named specialist → pre-mint per slice; LLM addresses each by name.
- You want **`delegate_task(background=True)`** to dispatch the actual work to an isolated sandbox with its own MEMORY, not into the Hermes gateway itself.

Not the right tool when:

- The task is one-shot and Hermes can answer directly.
- You need cross-subagent shared state (each subagent's MEMORY is its own).

## Routing model

Exactly two surfaces. Don't conflate them.

| Surface | Role |
|---|---|
| **`default_agent_name="general-worker"`** | Catch-all for unrouted delegations. Use only for a **generic** worker; the default's job is "send any background offload here, accumulate the session breadcrumb." |
| **`toolsets=["agentmint-<name>"]`** | Per-call specialist routing. LLM includes this in the toolsets list to send a particular call to a particular expert (e.g. `agentmint-pr-reviewer`). Each specialist has its own MEMORY.md. |

**Pattern discipline:** never name a specialist as `default_agent_name`. Specialists go through the toolsets directive; the default slot is generic. Naming a specialist as the default breaks the moment you add a second specialist.

## Operator setup (5 steps)

### Step 1 — bootstrap an AgentMint credit wallet (one-time, $1 minimum)

Any rail works. Pick whichever the operator has authenticated locally:

```bash
# Stripe-Link via link-cli:
link-cli mpp pay https://api.agentmint.store/a2a -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}'

# x402 Base via agentcash:
npx agentcash@latest fetch https://api.agentmint.store/a2a \
  -m POST -b '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}' \
  --payment-network base

# Tempo MPP via tempo-request:
~/.tempo/bin/tempo-request -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"credits.topup","params":{"amount_usd":5}}' \
  https://api.agentmint.store/a2a
```

Extract `result.access_token` from the response. Cache it:

```bash
export AGENTMINT_JWT=<the access_token>
mkdir -p ~/.agentmint && chmod 700 ~/.agentmint
echo "$AGENTMINT_JWT" > ~/.agentmint/jwt
chmod 600 ~/.agentmint/jwt
```

### Step 2 — install the runner

```bash
pip install agentmint-hermes-runner   # in Hermes' venv
```

### Step 3 — pre-mint a generic worker (catch-all)

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"agent.create",
    "params":{
      "name":"general-worker",
      "mode":"all-inclusive",
      "persona":"General-purpose worker. Handle whatever delegation you receive. Append a 1-2 sentence summary to /workspace/MEMORY.md after each meaningful run."
    }
  }' | jq '.result.agent_id'
```

Cost: $0.10 from your credit wallet.

### Step 4 — wire the adapter into Hermes startup

Add to your Hermes gateway startup code (the script that boots the gateway), **before** any `delegate_task` call:

```python
import os
from agentmint_hermes_runner import (
    AgentMintDispatcher, BearerAuth, install_delegate_task_wrapper,
)

dispatcher = AgentMintDispatcher(auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]))
install_delegate_task_wrapper(dispatcher, default_agent_name="general-worker")
```

Restart Hermes so the new module loads and the patch takes effect.

### Step 5 — verify

In a Hermes chat:

```
> Use delegate_task with background=True: "Say hello and tell me what you remember."
```

You should see the call dispatched to `general-worker`, polled until done, then re-injected as a new Hermes turn.

## PR review quickstart (the canonical demo)

Once steps 1-4 above are done, add the `pr-reviewer` specialist on top of the generic catch-all.

### Pre-mint the specialist

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"agent.create",
    "params":{
      "name":"pr-reviewer",
      "mode":"all-inclusive",
      "persona":"You review GitHub PRs. Follow the pr-review skill exactly.",
      "skills":["mesutcelik/agentmint-skills/pr-review"]
    }
  }' | jq '.result.agent_id'
```

Cost: another $0.10 from your wallet. The `mesutcelik/agentmint-skills/pr-review` skill ships the `fetch.sh` and `post.sh` scripts into `/workspace/home/pr-review/` inside the box.

### Tell Hermes' LLM the specialist exists

Add to your Hermes session persona (system prompt):

```
You have one background specialist available via delegate_task:

  - pr-reviewer — reviews GitHub PRs in any owner/repo. Use this for any
    "review PR X" request. To dispatch to it, include "agentmint-pr-reviewer"
    in the toolsets list AND ship the GitHub PAT via workspace_files:

      delegate_task(
          background=True,
          goal="Review PR <N> in <owner>/<repo>. Post a short comment.",
          toolsets=["terminal", "file", "agentmint-pr-reviewer"],
          workspace_files=[
              {"path": "/workspace/.github_pat", "content": "<the PAT>"}
          ],
      )

  The agent reads /workspace/.github_pat, fetches the PR diff via gh CLI,
  writes a review to /workspace/home/pr-review/review-out.md, and posts it
  to the PR via `gh pr comment`. Result returns to Hermes when done.
```

### Test it

From the Hermes chat:

```
> Review PR 12 in mesutcelik/agentmint-mono. Do it in the background via
  delegate_task using the pr-reviewer specialist. Ship the GitHub PAT —
  it's in $GH_PAT.
```

The runner dispatches asynchronously, polls AgentMint, and resumes the conversation when the review comment has been posted. Typical wall time: 20-60s for a small PR; longer for complex diffs.

### Verify

```bash
# Confirm the review comment landed
gh pr view <N> --repo <owner>/<repo> --comments --json comments \
  --jq '.comments[-1] | {author: .author.login, body}'

# Confirm AgentMint billing
curl -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -d '{"jsonrpc":"2.0","method":"credits.history","params":{"limit":3},"id":1}' \
  | jq '.result.entries[] | {kind, amount_usd: (.amount_microusdc/1e6), method}'
```

## Fleet management — beyond setup

The Hermes LLM can manage subagents directly via `terminal` + curl. The `delegate_task` patch only handles dispatching; for create / list / delete / inspect, use direct `/a2a` calls.

### List subagents owned by the calling principal

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.list","params":{}}'
```

### Add a new specialist

Same shape as the `general-worker` and `pr-reviewer` mints above. Pick a specific name (`reviewer-mesutcelik-mono`, `data-analyst-q3-sales`, …) so collisions don't happen as the fleet grows.

### Delete an unused specialist

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.delete","params":{"name":"some-name"}}'
```

$0.01 dust + tears down the sandbox.

### Dispatch to a specialist directly without Hermes

Useful for testing the specialist in isolation:

```bash
curl -X POST https://api.agentmint.store/a2a \
  -H "Authorization: Bearer $AGENTMINT_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.run","params":{
        "name":"pr-reviewer","prompt":"Review PR 12 in mesutcelik/agentmint-mono.",
        "workspace_files":[{"path":"/workspace/.github_pat","content":"<PAT>"}]
      }}'
```

## Hermes `delegate_task` coverage (runner v0.9.x)

Audited against the live Hermes delegation docs. Status notation: ✅ supported, ✅ soft hint = prompt-level only (sandbox can't structurally enforce), ❌ not implemented, n/a = different model that doesn't reach us.

### Call parameters

| Hermes feature | Status | Notes |
|---|---|---|
| `goal` | ✅ | Concatenated under `## Goal` in the synthesized prompt. |
| `context` | ✅ | Concatenated under `## Context`. |
| `toolsets=["terminal", "file"]` | ✅ soft hint | Prompt restriction lines ("Do not run shell commands"). |
| `toolsets=["web"]` | ❌ | Raises `UnsupportedToolset`. |
| `toolsets=["agentmint-<name>", ...]` | ✅ (workaround) | **Routing directive** — adapter parses `agentmint-<name>`, dispatches to that subagent, strips entry from toolsets. Upstream Hermes proposal filed (`docs/hermes-feature-request.md`); the directive becomes a first-class parameter once that lands. |
| `role="leaf"` / `"orchestrator"` | ✅ soft hint | Prompt-level only. |
| `max_iterations` | ✅ soft hint | Harness-dependent enforcement. |
| `tasks=[{...}, {...}]` batch | ✅ | `dispatch_batch` — ThreadPoolExecutor; results in input order. |
| `background=True` (PR #40946) | ✅ | The path we patch. |
| `workspace_files=[{path, content}, ...]` | ✅ | Files written into the sandbox before the run starts; max 10 files, 10 MB each. Used to ship PATs, configs, etc. |

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
| `delegate_task` blocks parent turn unless `background=True` | ✅ | Sync mirrors: `dispatch()` blocks until completion. Background is the only async path Hermes-side, and that's what we patch. |
| Interrupt cascade (parent `/stop` cancels all children) | ✅ | `cancel_event=threading.Event` fires `agent.cancel`. |
| Status `"interrupted"` on parent interrupt | ✅ | `DispatchResult.status="interrupted"`. |
| Hard-timeout diagnostic dumps | ❌ | We raise `DispatchTimeout`; no log file written. |

### Subagent restrictions

| Hermes feature | Status | Notes |
|---|---|---|
| Leaf-blocked tools (`delegation` / `clarify` / `memory` / `code_execution` / `send_message`) | n/a | AgentMint sandboxes don't expose Hermes' tool registry. Soft prompt hint only. |
| Orchestrator-blocked tools | n/a | Same. |
| Fresh conversation per call ("subagents know nothing") | **inverted** | This inversion is the AgentMint value prop — `/workspace/MEMORY.md` survives every dispatch to a named subagent. |
| Credential inheritance (parent's API key passed to children) | **different model** | Hermes: subagents inherit parent's API key. AgentMint: each sandbox uses AgentMint's server-managed stored keys — no parent credential leakage. |

### Hermes-side UI / observability

| Hermes feature | Status | Notes |
|---|---|---|
| `/agents` TUI overlay | partial | Dispatches go through `_async_delegation_watcher` for re-injection but don't currently register with `_active_subagents` (the TUI registry). Use `agent.list` / `agent.run.status` against AgentMint directly. |
| Per-branch cost / token rollups | partial | Available via `agent.runs` and `agent.run.status` (`billed_usdc` field) but not surfaced into Hermes' TUI. |
| `delegation.pause` RPC | n/a | Hermes-level; we don't observe it. |

## Pitfalls

- **One JWT per principal**, shared across every subagent that principal owns. Loss = `credits.rekey` ($0.01 over x402/Tempo MPP) or fresh `credits.topup` over Stripe-Link.
- **`name` is global + immutable.** First mint wins. Pick something specific (`pr-reviewer-mesutcelik-mono`, not `reviewer`). Released only by `agent.delete`.
- **Per-call pricing is end-of-run debit.** BYOK: flat $0.02. All-inclusive: actual provider cost (cache-aware estimate) + $0.02 platform fee.
- **Stripe topup carries a passthrough fee.** A $5 Stripe topup charges ~$5.30 on Stripe; wallet is credited $5.00. x402 and Tempo MPP settle 1:1.
- **Concurrency gate**: balance < $1 → 1 in-flight run per principal; ≥ $1 → 5. Topup to unlock parallel delegations.
- **`workspace_files` for secrets**: when shipping a GitHub PAT or similar, ship via `workspace_files` to `/workspace/.github_pat`. Don't embed in `goal` or `context`.
- **Don't name a specialist as `default_agent_name`.** See routing-model section above.

## Verification

```bash
# Confirm the AgentMint endpoint is reachable
curl -X POST https://api.agentmint.store/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"agent.create","params":{}}'
# → 402 with accepts[] enumerating supported rails

# Confirm the runner is importable in Hermes' venv
python -c "from agentmint_hermes_runner import install_delegate_task_wrapper; print('ok')"
```

For setup canaries, see `examples/persistent.py` in the [agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes) repo. The upstream Hermes proposal for a proper dispatcher arg on `delegate_task` lives in `docs/hermes-feature-request.md` in the same repo.
