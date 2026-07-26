"""LangGraph Adapter 辅助:Agent 构建兼容层、多轮调用与最终回答提取。

entrypoint 内部用法:
    agent = create_tool_agent(model, tools)   # 或你自己的构建逻辑
    return invoke_langgraph(agent, turns)
"""

from __future__ import annotations

import warnings

from langchain_core.messages import BaseMessage, HumanMessage


def create_tool_agent(model, tools):
    """构建工具调用 Agent,兼容新旧 API。

    优先 langchain v1 的 create_agent;未安装 langchain 时回退到
    langgraph.prebuilt.create_react_agent(LangGraph v1 中已标记废弃,
    v2 将移除 —— 本兼容层就是为这次迁移准备的)。
    """
    try:
        from langchain.agents import create_agent
        return create_agent(model, tools)
    except ImportError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from langgraph.prebuilt import create_react_agent
            return create_react_agent(model, tools)


def invoke_langgraph(agent, turns: list[str], recursion_limit: int = 25) -> str:
    """按轮次调用 LangGraph Agent,消息跨轮累积,返回最后一轮的最终回答。"""
    messages: list[BaseMessage] = []
    for turn in turns:
        messages.append(HumanMessage(content=turn))
        result = agent.invoke({"messages": messages}, {"recursion_limit": recursion_limit})
        messages = list(result["messages"])
    return str(messages[-1].content) if messages else ""
