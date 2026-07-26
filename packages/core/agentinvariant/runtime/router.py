"""工具执行虚拟化(POC 核心)。

把任意 LangChain/LangGraph BaseTool 包装为 VirtualTool,按策略路由到
live / mock / replay / blocked / record 五种模式,Agent 代码本身零改动 —
只需在构建 Agent 前对工具列表调用 virtualize()。

默认安全策略:未显式配置策略的工具一律 blocked
(见 docs/design-baseline.md 11.2)。
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Callable

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..fixtures.store import FixtureStore, schema_hash_of
from ..tracing.recorder import TraceRecorder


class ExecutionMode(str, Enum):
    LIVE = "live"
    MOCK = "mock"
    REPLAY = "replay"
    BLOCKED = "blocked"
    RECORD = "record"  # live 执行 + 落盘 Fixture


class ToolEffect(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE_REVERSIBLE = "WRITE_REVERSIBLE"
    WRITE_IRREVERSIBLE = "WRITE_IRREVERSIBLE"
    EXTERNAL_COMMUNICATION = "EXTERNAL_COMMUNICATION"
    CODE_EXECUTION = "CODE_EXECUTION"


class ToolPolicy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    mode: ExecutionMode
    effect: ToolEffect = ToolEffect.READ_ONLY
    mock_result: Any = None
    # 模拟延迟(仅 mock/replay 生效):复现慢工具、验证超时隔离与延迟预算
    latency_ms: float = 0
    # 参数守卫:返回 None 表示放行,返回字符串表示违规原因并阻断执行。
    # 与 Contract Engine 的 argument_constraint 同源(matchers 注册表),
    # 守卫在执行前阻断,契约在事后取证。
    argument_guard: Callable[[dict[str, Any]], str | None] | None = None


def _to_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


class VirtualTool(BaseTool):
    """包装真实工具,按 ToolPolicy 决定实际行为并记录 Trace。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _inner: BaseTool = PrivateAttr()
    _policy: ToolPolicy = PrivateAttr()
    _recorder: TraceRecorder = PrivateAttr()
    _store: FixtureStore | None = PrivateAttr(default=None)
    _schema_hash: str = PrivateAttr(default="")

    def __init__(
        self,
        inner: BaseTool,
        policy: ToolPolicy,
        recorder: TraceRecorder,
        store: FixtureStore | None = None,
    ) -> None:
        super().__init__(
            name=inner.name,
            description=inner.description,
            args_schema=inner.args_schema,
        )
        self._inner = inner
        self._policy = policy
        self._recorder = recorder
        self._store = store
        self._schema_hash = schema_hash_of(inner.args_schema)

    def _run(self, **kwargs: Any) -> str:
        policy = self._policy
        event = self._recorder.record(self.name, kwargs, policy.mode.value)
        event.effect = policy.effect.value

        if policy.mode is ExecutionMode.BLOCKED:
            event.violation = "tool blocked by policy"
            event.error = "blocked"
            return _to_content({"error": f"工具 {self.name} 已被测试策略阻断,未真实执行。"})

        if policy.argument_guard is not None:
            reason = policy.argument_guard(kwargs)
            if reason:
                event.violation = reason
                event.error = "argument_guard"
                return _to_content({"error": f"工具 {self.name} 参数违反策略: {reason},未执行。"})

        if policy.latency_ms and policy.mode in (ExecutionMode.MOCK, ExecutionMode.REPLAY):
            time.sleep(policy.latency_ms / 1000)

        if policy.mode is ExecutionMode.MOCK:
            event.result = policy.mock_result
            return _to_content(policy.mock_result)

        if policy.mode is ExecutionMode.REPLAY:
            if self._store is None:
                event.error = "no fixture store configured"
                return _to_content({"error": "replay 模式缺少 FixtureStore。"})
            hit, result, reason = self._store.lookup(self.name, kwargs, self._schema_hash)
            if not hit:
                event.error = reason
                detail = "工具 Schema 已变化,Fixture 过期" if reason and reason.startswith("fixture_stale") else "未找到历史 Fixture"
                return _to_content({"error": f"{detail},无法回放 {self.name}。"})
            event.result = result
            return _to_content(result)

        # LIVE / RECORD:真实执行
        result = self._inner.invoke(kwargs)
        event.result = result
        if policy.mode is ExecutionMode.RECORD:
            if self._store is None:
                raise RuntimeError("record 模式需要 FixtureStore")
            self._store.save(self.name, kwargs, result, schema_hash=self._schema_hash)
        return _to_content(result)


def virtualize(
    tools: list[BaseTool],
    policies: dict[str, ToolPolicy],
    recorder: TraceRecorder,
    store: FixtureStore | None = None,
) -> list[BaseTool]:
    """把工具列表包装为受策略控制的 VirtualTool 列表。

    未在 policies 中声明的工具默认 blocked(副作用默认安全)。
    """
    default = ToolPolicy(mode=ExecutionMode.BLOCKED)
    return [VirtualTool(tool, policies.get(tool.name, default), recorder, store) for tool in tools]
