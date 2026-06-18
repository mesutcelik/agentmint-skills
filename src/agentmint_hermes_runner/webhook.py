import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any, Protocol


class _Queue(Protocol):
    def put(self, item: Any) -> None: ...


def default_event_adapter(event: dict) -> dict:
    """Translate an AgentMint webhook payload into a Hermes async_delegation
    completion-queue event.

    This is the minimal shape Hermes' `_async_delegation_watcher` in
    `gateway/run.py` consumes (post-PR #40946). If your Hermes version
    expects a different shape, supply your own adapter to
    AgentMintWebhookReceiver(event_adapter=...).
    """
    return {
        "type": "async_delegation",
        "source": "agentmint",
        "delegation_id": event.get("delegation_id") or event.get("run_id"),
        "status": event.get("status", "completed"),
        "result": event.get("result"),
        "task_source": (event.get("metadata") or {}).get("hermes", {}),
        "agentmint_event": event,
    }


class AgentMintWebhookReceiver:
    """Verify AgentMint QStash webhooks and push completion events onto a
    Hermes process_registry.completion_queue.

    Wire-up:
        from hermes.gateway.process_registry import completion_queue
        receiver = AgentMintWebhookReceiver(
            signing_secret=os.environ["AGENTMINT_WEBHOOK_SIGNING_SECRET"],
            completion_queue=completion_queue,
        )

    Then in your HTTP route:
        status, body = receiver.handle(dict(request.headers), request.get_data())
        return body, status
    """

    SIG_HEADER = "X-AgentMint-Signature"
    TS_HEADER = "X-AgentMint-Timestamp"

    def __init__(
        self,
        signing_secret: str,
        completion_queue: _Queue,
        event_adapter: Callable[[dict], Any] | None = None,
        max_age_seconds: int = 300,
    ):
        if not signing_secret:
            raise ValueError("signing_secret is required")
        self.signing_secret = signing_secret.encode("utf-8")
        self.completion_queue = completion_queue
        self.event_adapter = event_adapter or default_event_adapter
        self.max_age_seconds = max_age_seconds

    def handle(self, headers: dict[str, str], body: bytes) -> tuple[int, dict]:
        sig, ts = self._extract_headers(headers)
        if not sig or not ts:
            return 400, {"error": "missing signature headers"}
        try:
            ts_int = int(ts)
        except ValueError:
            return 400, {"error": "bad timestamp"}
        if abs(int(time.time()) - ts_int) > self.max_age_seconds:
            return 401, {"error": "timestamp too old"}
        expected = hmac.new(
            self.signing_secret,
            f"{ts}.".encode() + body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return 401, {"error": "bad signature"}
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            return 400, {"error": "bad json"}
        self.completion_queue.put(self.event_adapter(event))
        return 200, {"ok": True}

    def _extract_headers(self, headers: dict[str, str]) -> tuple[str | None, str | None]:
        lookup = {k.lower(): v for k, v in headers.items()}
        return lookup.get(self.SIG_HEADER.lower()), lookup.get(self.TS_HEADER.lower())
