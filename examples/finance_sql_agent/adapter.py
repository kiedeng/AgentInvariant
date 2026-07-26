"""Python Callable Adapter 入口:fn(tools, scenario) -> 最终回答文本。

场景上下文以 JSON 首行注入第一轮输入(本示例的约定;正式版将由
统一 RunContext 承载)。input 支持单轮字符串或多轮列表。
"""

from __future__ import annotations

import json

from agentinvariant.adapters import invoke_langgraph
from langchain_core.tools import BaseTool

from .agents import build_agent_v1, build_agent_v2


def _turns(scenario: dict) -> list[str]:
    raw = scenario["input"]
    turns = [raw] if isinstance(raw, str) else list(raw)
    ctx = json.dumps(scenario.get("context", {}), ensure_ascii=False)
    return [f"{ctx}\n{turns[0]}", *turns[1:]]


def run_v1(tools: list[BaseTool], scenario: dict) -> str:
    return invoke_langgraph(build_agent_v1(tools), _turns(scenario))


def run_v2(tools: list[BaseTool], scenario: dict) -> str:
    return invoke_langgraph(build_agent_v2(tools), _turns(scenario))
