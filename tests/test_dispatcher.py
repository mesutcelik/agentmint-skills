import json

import pytest

from agentmint_hermes_runner.dispatcher import AgentMintDispatcher


class FakeAuth:
    def __init__(self, result: dict):
        self._result = result
        self.last_envelope: dict | None = None

    def call(self, endpoint: str, method: str, body: bytes) -> bytes:
        self.last_envelope = json.loads(body)
        return json.dumps({"jsonrpc": "2.0", "id": "x", "result": self._result}).encode()


def test_dispatch_async_requires_webhook_url():
    auth = FakeAuth({"status": "dispatched"})
    dispatcher = AgentMintDispatcher(auth=auth)
    with pytest.raises(ValueError, match="webhook_url"):
        dispatcher.dispatch(agent_name="hello-bot", goal="hi", async_=True)


def test_dispatch_async_passes_webhook_and_metadata():
    auth = FakeAuth({"status": "dispatched", "delegation_id": "del_1"})
    dispatcher = AgentMintDispatcher(auth=auth, webhook_url="https://hook.example/wh")
    result = dispatcher.dispatch(
        agent_name="hello-bot",
        goal="hi",
        async_=True,
        hermes_context={"session_key": "abc"},
        webhook_headers={"X-Custom": "1"},
    )
    assert result.status == "dispatched"
    assert result.delegation_id == "del_1"
    params = auth.last_envelope["params"]
    assert params["name"] == "hello-bot"
    assert params["prompt"] == "hi"
    assert params["async"] is True
    assert params["webhook"] == {"url": "https://hook.example/wh", "headers": {"X-Custom": "1"}}
    assert params["metadata"] == {"hermes": {"session_key": "abc"}}


def test_dispatch_sync_omits_webhook_block():
    auth = FakeAuth({"status": "ok"})
    dispatcher = AgentMintDispatcher(auth=auth)
    dispatcher.dispatch(agent_name="hello-bot", goal="hi")
    params = auth.last_envelope["params"]
    assert "webhook" not in params
    assert "async" not in params


def test_create_returns_agent_record():
    auth = FakeAuth({"agent_id": "agt_123", "name": "hello-bot", "harness": "opencode"})
    dispatcher = AgentMintDispatcher(auth=auth)
    agent = dispatcher.create(name="hello-bot")
    assert agent.agent_id == "agt_123"
    assert agent.name == "hello-bot"
    assert agent.harness == "opencode"


def test_list_returns_records():
    auth = FakeAuth({"count": 2, "agents": [{"agent_id": "agt_1"}, {"agent_id": "agt_2"}]})
    dispatcher = AgentMintDispatcher(auth=auth)
    agents = dispatcher.list()
    assert len(agents) == 2
    assert agents[0].agent_id == "agt_1"
