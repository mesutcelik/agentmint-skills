# agentmint-skills

A catalog of [Hermes](https://github.com/NousResearch/hermes-agent)-installable skills for [AgentMint](https://agentmint.store).

Each skill lives in its own subfolder containing a `SKILL.md`. Skills tell the Hermes agent how to do something with AgentMint; the actual implementation (Python adapter, CLI, etc.) lives in its own separate repo.

## Available skills

| Skill | What it does | Install |
|---|---|---|
| [`agentmint-hermes`](agentmint-hermes/SKILL.md) | Route Hermes `delegate_task(background=True)` to named, persistent AgentMint subagents | `hermes skills install mesutcelik/agentmint-skills/agentmint-hermes` |

## Related repos

- **[mesutcelik/agentmint-hermes](https://github.com/mesutcelik/agentmint-hermes)** — Python adapter (`agentmint-hermes-runner` on PyPI) that the `agentmint-hermes` skill installs and wires into Hermes' gateway.
- **AgentMint API** — full spec at <https://agentmint.store/SKILL.md> (canonical for wallets, payment rails, every JSON-RPC method).

## Adding a new skill

1. Create a new subfolder named after the skill (must match the `name:` in the SKILL.md frontmatter).
2. Drop a `SKILL.md` inside, following the [Hermes skill format](https://hermes-agent.nousresearch.com/docs/user-guide/skills) (frontmatter + procedural body).
3. Reference the implementation by its package name (PyPI, npm, etc.) — don't bundle code here.
4. Add an entry to the table above.
5. Commit + push. Hermes' `GitHubSource` picks it up via `hermes skills install mesutcelik/agentmint-skills/<skill-name>`.

## License

MIT
