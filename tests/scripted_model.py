"""A stand-in for the Anthropic client. It replays a script of responses so the agent loop,
tools, calendar and database can be tested without a network or an API key."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Block:
    data: dict

    def model_dump(self) -> dict:
        return self.data


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str


@dataclass
class ScriptedMessages:
    script: list[list[dict[str, Any]]]
    calls: list[dict] = field(default_factory=list)
    _i: int = 0

    def create(self, **kwargs) -> _Response:
        self.calls.append(kwargs)
        step = self.script[self._i]
        self._i += 1
        blocks = [_Block(b) for b in step]
        stop = "tool_use" if any(b["type"] == "tool_use" for b in step) else "end_turn"
        return _Response(blocks, stop)


@dataclass
class ScriptedClient:
    messages: ScriptedMessages


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def tool(tool_name: str, tool_id: str, **inputs) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": tool_name, "input": inputs}
