import hashlib
import hmac
import json
import time
from queue import Queue

from agentmint_hermes_runner.webhook import AgentMintWebhookReceiver

SECRET = "test-secret"


def _sign(body: bytes, ts: int | None = None) -> tuple[str, str]:
    ts = ts if ts is not None else int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return str(ts), sig


def test_handle_accepts_valid_signature():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(signing_secret=SECRET, completion_queue=q)
    body = json.dumps(
        {"delegation_id": "del_1", "status": "completed", "result": "ok"}
    ).encode()
    ts, sig = _sign(body)
    status, _ = r.handle({"X-AgentMint-Signature": sig, "X-AgentMint-Timestamp": ts}, body)
    assert status == 200
    assert q.qsize() == 1
    event = q.get_nowait()
    assert event["type"] == "async_delegation"
    assert event["delegation_id"] == "del_1"
    assert event["source"] == "agentmint"


def test_handle_rejects_bad_signature():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(signing_secret=SECRET, completion_queue=q)
    body = b'{"x":1}'
    ts, _ = _sign(body)
    status, _ = r.handle({"X-AgentMint-Signature": "bad", "X-AgentMint-Timestamp": ts}, body)
    assert status == 401
    assert q.qsize() == 0


def test_handle_rejects_old_timestamp():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(signing_secret=SECRET, completion_queue=q, max_age_seconds=60)
    body = b'{"x":1}'
    old_ts = int(time.time()) - 3600
    ts_str, sig = _sign(body, ts=old_ts)
    status, _ = r.handle({"X-AgentMint-Signature": sig, "X-AgentMint-Timestamp": ts_str}, body)
    assert status == 401
    assert q.qsize() == 0


def test_handle_rejects_missing_headers():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(signing_secret=SECRET, completion_queue=q)
    status, _ = r.handle({}, b'{"x":1}')
    assert status == 400


def test_handle_is_case_insensitive_for_headers():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(signing_secret=SECRET, completion_queue=q)
    body = b'{"delegation_id":"del_2","status":"completed"}'
    ts, sig = _sign(body)
    status, _ = r.handle({"x-agentmint-signature": sig, "x-agentmint-timestamp": ts}, body)
    assert status == 200


def test_custom_event_adapter():
    q: Queue = Queue()
    r = AgentMintWebhookReceiver(
        signing_secret=SECRET,
        completion_queue=q,
        event_adapter=lambda e: {"custom": True, "id": e["delegation_id"]},
    )
    body = json.dumps({"delegation_id": "del_3", "status": "completed"}).encode()
    ts, sig = _sign(body)
    r.handle({"X-AgentMint-Signature": sig, "X-AgentMint-Timestamp": ts}, body)
    event = q.get_nowait()
    assert event == {"custom": True, "id": "del_3"}
