# agentmint-hermes-runner

Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents.

> Positioning + full quickstart to come — see `docs/SKILL.md` for the current Hermes-readable spec.

## Status

v0.1.0 — alpha. Auth backends: `BearerAuth` (Stripe-Link), `TempoAuth` (Tempo USDC.e).

## Install

```bash
pip install agentmint-hermes-runner
```

## Test

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
