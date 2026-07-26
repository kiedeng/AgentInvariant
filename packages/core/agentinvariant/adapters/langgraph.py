"""LangGraph Adapter 辅助:多轮调用与最终回答提取。

entrypoint 内部用法:
    agent = build_agent(tools)
    return invoke_langgraph(agent, turns)
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage


def invoke_langgraph(agent, turns: list[str], recursion_limit: int = 25) -> str:
    """按轮次调用 LangGraph Agent,消息跨轮累积,返回最后一轮的最终回答。"""
    messages: list[BaseMessage] = []
    for turn in turns:
        messages.append(HumanMessage(content=turn))
        result = agent.invoke({"messages": messages}, {"recursion_limit": recursion_limit})
        messages = list(result["messages"])
    return str(messages[-1].content) if messages else ""
