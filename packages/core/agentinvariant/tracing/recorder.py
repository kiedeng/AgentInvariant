"""极简运行内 Trace 记录器。

正式版应使用 OpenTelemetry / OpenInference Span(见 docs/design-baseline.md 8.2);
POC 阶段只需要一个可比较的结构化工具调用序列。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallEvent:
    index: int
    tool: str
    args: dict[str, Any]
    mode: str
    result: Any = None
    error: str | None = None
    violation: str | None = None
    effect: str = "READ_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "args": self.args,
            "mode": self.mode,
            "result": self.result,
            "error": self.error,
            "violation": self.violation,
            "effect": self.effect,
        }


class TraceRecorder:
    """单次 Agent 运行的工具调用记录。"""

    def __init__(self) -> None:
        self.events: list[ToolCallEvent] = []

    def record(self, tool: str, args: dict[str, Any], mode: str) -> ToolCallEvent:
        event = ToolCallEvent(index=len(self.events), tool=tool, args=args, mode=mode)
        self.events.append(event)
        return event

    @property
    def tool_sequence(self) -> list[str]:
        return [e.tool for e in self.events]

    @property
    def violations(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events if e.violation]

    def to_dict(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]
