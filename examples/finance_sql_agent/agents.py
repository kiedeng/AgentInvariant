"""Baseline (V1) 与 Candidate (V2) Agent。

关键点:Agent 构建代码对虚拟化零感知 —— 它只接收一个工具列表。
调用方(测试引擎)在传入前用 virtualize() 包装工具,即完成截获。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from .scripted_model import ScriptedFinanceModel


def build_agent_v1(tools: list[BaseTool]):
    """V1:指标识别 -> SQL -> 回答(无权限检查)。"""
    return create_react_agent(ScriptedFinanceModel(require_permission=False), tools)


def build_agent_v2(tools: list[BaseTool]):
    """V2:指标识别 -> 权限检查 -> SQL -> 回答。"""
    return create_react_agent(ScriptedFinanceModel(require_permission=True), tools)
