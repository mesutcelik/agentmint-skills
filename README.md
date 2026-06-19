# agentmint-skills

A catalog of skills that consume the [AgentMint](https://agentmint.store) API. Any agent-framework's skill format is welcome — Hermes, Claude Code, Cursor, OpenCode, Codex, raw MCP, etc.

Each skill lives in its own subfolder containing a `SKILL.md` (procedural instructions in markdown + frontmatter). The repo is markdown-only — actual implementation code (Python adapter, CLI, etc.) lives in its own separate repo.

## Available skills

| Skill | Target framework | What it does | Install |
|---|---|---|---|
| [`agentmint-hermes`](agentmint-hermes/SKILL.md) | Hermes Agent | Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents | `hermes skills install mesutcelik/agentmint-skills/agentmint-hermes` |

## Related repos

- **[mesutcelik/agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes)** — Python adapter (`agentmint-hermes-runner` on PyPI) that the `agentmint-hermes` skill installs and wires into Hermes' gateway.
- **AgentMint API** — full spec at <https://agentmint.store/SKILL.md> (canonical for wallets, payment rails, every JSON-RPC method). Skills targeting any framework consume this.

## Adding a new skill

1. Create a new subfolder named after the skill (must match the `name:` in the SKILL.md frontmatter, if your framework expects one).
2. Drop a `SKILL.md` inside following your target framework's skill format — each agent framework has its own conventions for frontmatter, sections, etc.
3. Reference any implementation code by its package name (PyPI, npm, etc.) — don't bundle code in this repo.
4. Add a row to the table above with the target framework + install command.
5. Commit + push.

## License

MIT
