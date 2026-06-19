# agentmint-skills

A catalog of skills that consume the [AgentMint](https://agentmint.store) API. Any agent-framework's skill format is welcome — Hermes, Claude Code, Cursor, OpenCode, Codex, raw MCP, etc.

Each skill lives in its own subfolder containing a `SKILL.md` (procedural instructions in markdown + frontmatter). The repo is markdown-only — actual implementation code (Python adapter, CLI, etc.) lives in its own separate repo.

## Available skills

| Skill | Target | What it does | Install (Hermes example) |
|---|---|---|---|
| [`agentmint`](agentmint/SKILL.md) | Any agent framework | The canonical, universal AgentMint usage skill — discovery checklist, wallet matrix, every JSON-RPC method, persona format. Snapshot of <https://agentmint.store/SKILL.md>. | `hermes skills install mesutcelik/agentmint-skills/agentmint` |
| [`hermes-delegate-task`](hermes-delegate-task/SKILL.md) | Hermes Agent | Route Hermes `delegate_task(background=True)` to a named, persistent AgentMint subagent that REMEMBERS across calls. | `hermes skills install mesutcelik/agentmint-skills/hermes-delegate-task` |

## Related repos

- **[mesutcelik/agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes)** — Python adapter (`agentmint-hermes-runner` on PyPI) that the `hermes-delegate-task` skill installs and wires into Hermes' gateway.
- **AgentMint API** — canonical spec at <https://agentmint.store/SKILL.md> (served from `apps/web/public/SKILL.md` in the AgentMint mono-repo). The `agentmint` skill above is a periodic snapshot of this URL.

## Adding a new skill

1. Create a new subfolder named after the skill (must match the `name:` in the SKILL.md frontmatter, if your target framework expects one).
2. Drop a `SKILL.md` inside following your target framework's skill format — each framework has its own conventions for frontmatter, sections, etc.
3. Reference any implementation code by its package name (PyPI, npm, etc.) — don't bundle code in this repo.
4. Add a row to the table above with the target framework + install command.
5. Commit + push.

## License

MIT
