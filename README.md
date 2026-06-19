# agentmint-hermes-runner

Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents.

> Positioning + full quickstart in `docs/SKILL.md`.

## Status

**v0.4.0** — alpha. Auth backends: `BearerAuth` (Stripe-Link), `TempoAuth` (Tempo USDC.e). Polling-only delivery. Hermes feature coverage matrix in [`docs/SKILL.md`](docs/SKILL.md).

## Three-line Hermes wiring (Strategy B)

```python
import os
from agentmint_hermes_runner import (
    AgentMintDispatcher, BearerAuth, install_delegate_task_wrapper,
)

dispatcher = AgentMintDispatcher(auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]))
install_delegate_task_wrapper(dispatcher, default_agent_name="default-worker")
```

Every `delegate_task(background=True)` inside Hermes now routes to AgentMint's `default-worker` subagent. Its `/workspace/MEMORY.md` accumulates across every delegation. No HTTPS, no ngrok, no webhook secret — a daemon thread polls `agent.run.status` (free, Bearer-only) every 5 s and pushes completions onto Hermes' `completion_queue` directly. Server-side requires AgentMint API ≥ 0.7.0 for the polling endpoint.

## Install

```bash
pip install agentmint-hermes-runner
```

## Surface

```python
from agentmint_hermes_runner import (
    AgentMintDispatcher,
    AgentMintWebhookReceiver,
    BearerAuth, TempoAuth,
    Task,
)

dispatcher = AgentMintDispatcher(
    auth=BearerAuth(jwt=os.environ["AGENTMINT_JWT"]),
    webhook_url="https://my-gateway.example.com/agentmint-webhook",  # optional
)

# Single dispatch (Hermes delegate_task analog):
result = dispatcher.dispatch(
    agent_name="reviewer-myrepo",
    goal="Review the diff in /workspace/pr-42 and flag risks.",
    context="Project at /workspace, Python 3.11, uses Flask + PyJWT.",
    toolsets=["terminal", "file"],   # "web" raises UnsupportedToolset in v0.2
    role="leaf",                      # or "orchestrator"
    max_iterations=50,
    child_timeout_seconds=600,        # floor 30s; fires agent.cancel on expiry
)

# Batch dispatch (Hermes tasks=[…] analog):
results = dispatcher.dispatch_batch(
    tasks=[
        Task(agent_name="researcher-wasm", goal="WASM 2026 survey", context="…"),
        Task(agent_name="researcher-riscv", goal="RISC-V 2026 survey", context="…"),
    ],
    max_concurrent_children=3,
    child_timeout_seconds=900,
)
# results in input order; failed/timeout/interrupted statuses returned in-band
```

## Test

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Known unsupported (v0.2)

- **`toolsets=["web"]`** — no canonical AgentMint web-fetch skill yet. The supported harnesses (claude-code / codex / opencode) all have built-in web access via the harness itself, but we don't expose a Hermes-symmetric toolset for it. Raises `UnsupportedToolset` at compose time so the gap is loud, not silent.
- **`max_spawn_depth`** — AgentMint sandboxes aren't structurally bounded by depth.

## License

MIT
