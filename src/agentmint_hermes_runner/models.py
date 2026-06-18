from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class AgentRecord:
    agent_id: str
    name: str | None = None
    mode: str | None = None
    harness: str | None = None
    model: str | None = None
    runtime: str | None = None
    size: str | None = None
    created_at: int | None = None
    last_used: int | None = None
    lifetime_runs: int | None = None
    lifetime_billed_usdc: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentRecord":
        known = {f.name for f in fields(cls)} - {"extra"}
        kwargs = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(**kwargs, extra=extra)


@dataclass
class DispatchResult:
    status: str | None = None
    delegation_id: str | None = None
    run_id: str | None = None
    result: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "DispatchResult":
        known = {f.name for f in fields(cls)} - {"extra"}
        kwargs = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(**kwargs, extra=extra)
