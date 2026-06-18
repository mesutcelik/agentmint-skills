from typing import Any

from .auth.base import Auth
from .client import Client
from .models import AgentRecord, DispatchResult


class AgentMintDispatcher:
    """High-level wrapper around AgentMint's /a2a JSON-RPC surface.

    One dispatcher per (endpoint, auth, webhook_url) triple. Methods map 1:1
    to /a2a methods documented at https://agentmint.store/SKILL.md.
    """

    def __init__(
        self,
        auth: Auth,
        endpoint: str = "https://api.agentmint.store/a2a",
        webhook_url: str | None = None,
    ):
        self.client = Client(endpoint, auth)
        self.webhook_url = webhook_url

    def create(self, name: str, **kwargs: Any) -> AgentRecord:
        params = {"name": name, **kwargs}
        result = self.client.call("agent.create", params)
        return AgentRecord.from_dict(result or {})

    def get(self, agent_name: str) -> AgentRecord:
        result = self.client.call("agent.get", {"name": agent_name})
        return AgentRecord.from_dict(result or {})

    def list(self, limit: int = 50, offset: int = 0) -> list[AgentRecord]:
        result = self.client.call("agent.list", {"limit": limit, "offset": offset})
        agents = (result or {}).get("agents", [])
        return [AgentRecord.from_dict(a) for a in agents]

    def delete(self, agent_name: str) -> None:
        self.client.call("agent.delete", {"name": agent_name})

    def dispatch(
        self,
        agent_name: str,
        goal: str,
        files: list[dict] | None = None,
        cleanup_paths: list[str] | None = None,
        async_: bool = False,
        hermes_context: dict | None = None,
        webhook_headers: dict[str, str] | None = None,
    ) -> DispatchResult:
        """Run a subagent. By default synchronous; pass async_=True to dispatch
        in the background and receive completion via webhook."""
        params: dict[str, Any] = {"name": agent_name, "prompt": goal}
        if files:
            params["files"] = files
        if cleanup_paths:
            params["cleanup_paths"] = cleanup_paths
        if async_:
            if not self.webhook_url:
                raise ValueError("webhook_url is required on the dispatcher for async dispatch")
            params["async"] = True
            webhook: dict[str, Any] = {"url": self.webhook_url}
            if webhook_headers:
                webhook["headers"] = webhook_headers
            params["webhook"] = webhook
        if hermes_context:
            params["metadata"] = {"hermes": hermes_context}
        result = self.client.call("agent.run", params)
        return DispatchResult.from_dict(result or {})
